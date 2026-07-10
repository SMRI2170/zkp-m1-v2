// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract Groth16Verifier {
    // Scalar field size
    uint256 constant r    = 21888242871839275222246405745257275088548364400416034343698204186575808495617;
    // Base field size
    uint256 constant q   = 21888242871839275222246405745257275088696311157297823662689037894645226208583;

    // Verification Key data
    uint256 constant alphax  = 17103294384243930587309481628192561049644715909488494354088875202793441944880;
    uint256 constant alphay  = 11543737060872425228424550143370771184733652938189400017917235354998502308247;
    uint256 constant betax1  = 10994368876913771736943759526363135332295879807711621419532478321733458931214;
    uint256 constant betax2  = 6671825838784664772016588148644154568815848230926887679885529367708640934741;
    uint256 constant betay1  = 11745385433510845623213980851161272748406567854826676448220780423705152249655;
    uint256 constant betay2  = 4611672396731600699537220779158885822227303803177990269442457722832975850017;
    uint256 constant gammax1 = 11559732032986387107991004021392285783925812861821192530917403151452391805634;
    uint256 constant gammax2 = 10857046999023057135944570762232829481370756359578518086990519993285655852781;
    uint256 constant gammay1 = 4082367875863433681332203403145435568316851327593401208105741076214120093531;
    uint256 constant gammay2 = 8495653923123431417604973247489272438418190587263600148770280649306958101930;
    uint256 constant deltax1 = 1496227039560815393135457431748598669959348982144765446729595807336729486999;
    uint256 constant deltax2 = 14736164016421414611314564957725854235654023374666662862518384468815698108278;
    uint256 constant deltay1 = 12583800875640570172697070336230249463833362203268141930075666501231869443371;
    uint256 constant deltay2 = 16929504485702611350871485428841519849971658301101700938032958074784811141602;

    
    uint256 constant IC0x = 19039567582265007036634181801625386995684106977546730285772344701837927960202;
    uint256 constant IC0y = 16829969803302478905662054969997738858607767577429219892667504678405864177929;
    
    uint256 constant IC1x = 12888037524956918392195660746600923920144467098584817415838282312954721386176;
    uint256 constant IC1y = 16368456178807769026338788277594368990988356304246115528769570457405115800995;
    
    uint256 constant IC2x = 20284427795369939023471868183984117625027243188630731818400685626823328829450;
    uint256 constant IC2y = 9387774319414178604150684548925508665714400381511636827414705474696910822929;
    
    uint256 constant IC3x = 12330713678537446335868765498107944339710174212780799901016632318180741350530;
    uint256 constant IC3y = 6040887011466786419095117648503536328656462357136351060378317230885704628434;
    
    uint256 constant IC4x = 7970363155296867879563292083740893270315817113034326085715421241202918790497;
    uint256 constant IC4y = 4955772371639818767409958129757081060460207929830764714905022753086504519433;
    
    uint256 constant IC5x = 6637018516761373982315894477900723069589931238573733522595945293495268415997;
    uint256 constant IC5y = 932990976796599958086025023471783675590430511352244057197981012735104255620;
    
    uint256 constant IC6x = 10475379071558160094045707937549595473327868147112202125269580503012229462450;
    uint256 constant IC6y = 6750851476538424366404213113839168411204810761585900437516878048987223023176;
    
    uint256 constant IC7x = 10765320713399364905986663376398509581832188684873080071290878073646217788386;
    uint256 constant IC7y = 20786381973538379858834890002502800906544172188754881654754159498269623823954;
    
    uint256 constant IC8x = 8841465381575388437198339249627924503721810088475511846700180254019152170851;
    uint256 constant IC8y = 3114196839386809566001435054858691207971071298745402829824952141640735960543;
    
    uint256 constant IC9x = 21311253929251966480952115581118704761803768867600518173784290920540764024020;
    uint256 constant IC9y = 14359252706387565034014821964882144646183347805652654997489038272507417391565;
    
    uint256 constant IC10x = 21364478130257736994404373557536814974654274717602699805795079999415191883026;
    uint256 constant IC10y = 2342117755675028142695820389148314387246635396672268955392377956499190041316;
    
    uint256 constant IC11x = 21347580043685477076255927921207797567587167136857980397692474628475941267170;
    uint256 constant IC11y = 5096741156647130984662040501817727762237786546356000956560648681286911580705;
    
    uint256 constant IC12x = 21671660736169491567826559926148207349559078725492204216865840050806371297017;
    uint256 constant IC12y = 13769987773978210275301005077030885005311620431139378118548229657547383687047;
    
    uint256 constant IC13x = 7722110841900522671224891919387405747117511203160917952110768715842610544255;
    uint256 constant IC13y = 4054848928139648337724107606662320525117364091842418977513684454223089401634;
    
    uint256 constant IC14x = 15368947016804640383304772213714229682912651926354488178384670295987264557658;
    uint256 constant IC14y = 15459436384263603127919454532957990067125715878315646017021041160261320418750;
    
    uint256 constant IC15x = 5281325092154510252598438098754439355236440645055774322188961613164589028065;
    uint256 constant IC15y = 7080543238537398577530386033645618645389625530404450215511051233963115879470;
    
 
    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(uint[2] calldata _pA, uint[2][2] calldata _pB, uint[2] calldata _pC, uint[15] calldata _pubSignals) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }
            
            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x
                
                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))
                
                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))
                
                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))
                
                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))
                
                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))
                
                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))
                
                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))
                
                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))
                
                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))
                
                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))
                
                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))
                
                g1_mulAccC(_pVk, IC12x, IC12y, calldataload(add(pubSignals, 352)))
                
                g1_mulAccC(_pVk, IC13x, IC13y, calldataload(add(pubSignals, 384)))
                
                g1_mulAccC(_pVk, IC14x, IC14y, calldataload(add(pubSignals, 416)))
                
                g1_mulAccC(_pVk, IC15x, IC15y, calldataload(add(pubSignals, 448)))
                

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))


                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)


                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F
            
            checkField(calldataload(add(_pubSignals, 0)))
            
            checkField(calldataload(add(_pubSignals, 32)))
            
            checkField(calldataload(add(_pubSignals, 64)))
            
            checkField(calldataload(add(_pubSignals, 96)))
            
            checkField(calldataload(add(_pubSignals, 128)))
            
            checkField(calldataload(add(_pubSignals, 160)))
            
            checkField(calldataload(add(_pubSignals, 192)))
            
            checkField(calldataload(add(_pubSignals, 224)))
            
            checkField(calldataload(add(_pubSignals, 256)))
            
            checkField(calldataload(add(_pubSignals, 288)))
            
            checkField(calldataload(add(_pubSignals, 320)))
            
            checkField(calldataload(add(_pubSignals, 352)))
            
            checkField(calldataload(add(_pubSignals, 384)))
            
            checkField(calldataload(add(_pubSignals, 416)))
            
            checkField(calldataload(add(_pubSignals, 448)))
            

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
             return(0, 0x20)
         }
     }
 }
