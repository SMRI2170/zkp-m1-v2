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
    uint256 constant alphax  = 11048731929730407738202426498389736785625203458306758616549118013608925732923;
    uint256 constant alphay  = 13435098360980582996631118989196868555133437870265826284147375992763186149358;
    uint256 constant betax1  = 20129088473174089494863541977853323119322203238534605854283053981849009426878;
    uint256 constant betax2  = 13804107145552222758113248737828845008702039701256391706632640634471808207712;
    uint256 constant betay1  = 20804386932501344928782786436544688824143181663359623118116759652446059430315;
    uint256 constant betay2  = 12503330411884351549367648750543243840024558382297264474129116853229625909761;
    uint256 constant gammax1 = 11559732032986387107991004021392285783925812861821192530917403151452391805634;
    uint256 constant gammax2 = 10857046999023057135944570762232829481370756359578518086990519993285655852781;
    uint256 constant gammay1 = 4082367875863433681332203403145435568316851327593401208105741076214120093531;
    uint256 constant gammay2 = 8495653923123431417604973247489272438418190587263600148770280649306958101930;
    uint256 constant deltax1 = 1917010023311827952430024678321477314788161991501109887102926383637079046221;
    uint256 constant deltax2 = 7702824630669312042423476734331419872862909106972736245109957138903812124814;
    uint256 constant deltay1 = 18561802374002981036457657200784008025562203273502080410069235247858614254271;
    uint256 constant deltay2 = 14702299593138185917505650537787932926544474265064349721907827824784533367102;

    
    uint256 constant IC0x = 7718827981056861835926581276296276062949662486885634413881752772474065749688;
    uint256 constant IC0y = 11314256568578324445719770860893217784458419110212154337537055392463055933795;
    
    uint256 constant IC1x = 18718888555972860320271876402738254295162279716752619213622312431466001643947;
    uint256 constant IC1y = 21874465310250261636889380679481583510868506744576045925356038348268781137367;
    
    uint256 constant IC2x = 13503068745149023176429874464970442767633013416465912152592781602871998237488;
    uint256 constant IC2y = 9974291884452282443357181883673388340895344276858729646288467292284361631955;
    
    uint256 constant IC3x = 10554278735709037778228447283712120230770002349187109726738239700640550830566;
    uint256 constant IC3y = 1369604039151558585967075002371492696530440970297365698944496109297239873713;
    
    uint256 constant IC4x = 3160813863392977992909427506541059159726637348997076408702865500295659439862;
    uint256 constant IC4y = 7089579297745653845267442857312537662970977129636668726637272682880741785714;
    
    uint256 constant IC5x = 7252541362654408347674920162400933590003279420284377396687060636102134646037;
    uint256 constant IC5y = 18286256670739681636371808257031464752075172346471083223008451352854321295032;
    
    uint256 constant IC6x = 19563874189671409319699681594985176928478168609072394604214273620504314452246;
    uint256 constant IC6y = 11462034647823981260009463400343555677002264542962981435320848507853647293049;
    
    uint256 constant IC7x = 1830028897499661970557924546018330859544484431118179088669569422102687874841;
    uint256 constant IC7y = 11738626300853376862272216445588427951459094180407243815176017277398343500024;
    
    uint256 constant IC8x = 19028994988733617205710357606459743648881953100496357651890293406028237592048;
    uint256 constant IC8y = 10425473485961574409300570733972332958455264828411071325764389623867407866609;
    
    uint256 constant IC9x = 7358429862045730963176085746411888314820427155628758306970446641817267203276;
    uint256 constant IC9y = 1369883971696365800512662169440289908645654441262856374492413523460128790778;
    
    uint256 constant IC10x = 12770964804250662200445953144777728147170309499318913656870943450160772213348;
    uint256 constant IC10y = 21568048090681626015976396381292742176037627057261683535423170776904495528728;
    
    uint256 constant IC11x = 8290949566953597351166400865297262400850633045801807843344939456924245735149;
    uint256 constant IC11y = 21557005136215832609935116722993747765734409512642613038246705147614209125669;
    
    uint256 constant IC12x = 21659651313152780037870984606925823031143065397099024702899577963509857078133;
    uint256 constant IC12y = 13080110530793316676056398688745456510182636278669675292740780151453262723433;
    
    uint256 constant IC13x = 17502935264679384565597080664967353719289111761964943311810873359538265611258;
    uint256 constant IC13y = 19952686849575120472737827867529832631592808979193211443119471248277498851251;
    
    uint256 constant IC14x = 18041176240816190231131062393439260985318435093426148864547170103378942171704;
    uint256 constant IC14y = 2845815635625000703854613791563995649695695920782674929858235044672088342103;
    
    uint256 constant IC15x = 12092148631664237799249744756027375720260694150116374436610466368056062067797;
    uint256 constant IC15y = 2457484320800126516642903258131810312748380258736563836023503125740705033935;
    
    uint256 constant IC16x = 21343771769126586847350693960193198734957857426682836523693687073221409028344;
    uint256 constant IC16y = 19488466334155483511093743784235585751066348347568031838574699182634089311709;
    
    uint256 constant IC17x = 4599849634912783026366512682978374301518331194805744504541679365148853742079;
    uint256 constant IC17y = 6189238660283902814044986924078289102916741256712014995193259390324227030812;
    
    uint256 constant IC18x = 13459981324251880911541413560831557644572866501862428327525741719043373708390;
    uint256 constant IC18y = 20214005140831972323888037754823605127188920283490635130455857000009134906584;
    
 
    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(uint[2] calldata _pA, uint[2][2] calldata _pB, uint[2] calldata _pC, uint[18] calldata _pubSignals) public view returns (bool) {
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
                
                g1_mulAccC(_pVk, IC16x, IC16y, calldataload(add(pubSignals, 480)))
                
                g1_mulAccC(_pVk, IC17x, IC17y, calldataload(add(pubSignals, 512)))
                
                g1_mulAccC(_pVk, IC18x, IC18y, calldataload(add(pubSignals, 544)))
                

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
            
            checkField(calldataload(add(_pubSignals, 480)))
            
            checkField(calldataload(add(_pubSignals, 512)))
            
            checkField(calldataload(add(_pubSignals, 544)))
            

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
             return(0, 0x20)
         }
     }
 }
